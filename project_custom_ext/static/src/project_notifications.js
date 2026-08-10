/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { RPCError } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { UncaughtPromiseError } from "@web/core/errors/error_service";
import { FormController } from "@web/views/form/form_controller";

const PROJECT_EXCEPTIONS = new Set([
    "odoo.exceptions.AccessError",
    "odoo.exceptions.UserError",
    "odoo.exceptions.ValidationError",
]);

const PROJECT_MODEL_RE = /^project(\.|_)/;

/**
 * @param {RPCError} error
 */
function isProjectContextError(error) {
    if (error.model && PROJECT_MODEL_RE.test(error.model)) {
        return true;
    }
    const text = `${error.data?.message || ""} ${error.message || ""}`;
    return /project\.(project|task|task\.type|project_stage|milestone|update|tags|role|task\.template)/i.test(text)
        || /\b(Task Stage|Project Task|Project Template|Task Template|Stage Template)\b/i.test(text);
}

/**
 * @param {RPCError|{data?: {message?: string, name?: string}, message?: string, exceptionName?: string}} error
 */
export function friendlyProjectErrorMessage(error) {
    const raw = error.data?.message || error.message || "";
    const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
    const accessLine = lines.find((l) => /doesn'?t have/i.test(l));
    if (accessLine) {
        const permMatch = accessLine.match(/'(\w+)' access/);
        const permission = permMatch ? permMatch[1] : "access";
        const resourceLine = lines.find((l) => l.startsWith("-"));
        const resource = resourceLine ? resourceLine.replace(/^-\s*/, "") : _t("this item");
        return _t("You don't have %(permission)s permission on %(resource)s.", {
            permission,
            resource,
        });
    }
    const withoutBoilerplate = lines.filter(
        (l) => !/top-secret|Uh-oh|stumbled upon/i.test(l)
    );
    return withoutBoilerplate[0] || _t("This action is not allowed.");
}

function notificationTitle(error) {
    const name = error.exceptionName || error.data?.name || "";
    if (name.includes("ValidationError")) {
        return _t("Validation");
    }
    if (name.includes("AccessError")) {
        return _t("Not allowed");
    }
    return _t("Notice");
}

function showProjectNotification(env, error) {
    env.services.notification.add(friendlyProjectErrorMessage(error), {
        type: "warning",
        title: notificationTitle(error),
    });
}

function isHandledProjectError(error) {
    const name = error.exceptionName || error.data?.name || "";
    return PROJECT_EXCEPTIONS.has(name);
}

/**
 * Snackbar instead of modal dialogs for project-related UserError, ValidationError, AccessError.
 */
function projectRpcErrorHandler(env, error, originalError) {
    if (!(error instanceof UncaughtPromiseError) || !(originalError instanceof RPCError)) {
        return false;
    }
    if (!isHandledProjectError(originalError)) {
        return false;
    }
    if (!isProjectContextError(originalError)) {
        return false;
    }
    error.unhandledRejectionEvent.preventDefault();
    showProjectNotification(env, originalError);
    return true;
}

registry.category("error_handlers").add("projectRpcErrorHandler", projectRpcErrorHandler, {
    sequence: 96,
});

patch(FormController.prototype, {
    async onSaveError(error, callbacks, leaving) {
        const resModel = this.model.root.resModel;
        const inProjectArea =
            resModel?.startsWith("project.") || PROJECT_MODEL_RE.test(resModel || "");
        if (inProjectArea && isHandledProjectError(error)) {
            showProjectNotification(this.env, error);
            return;
        }
        return super.onSaveError(error, callbacks, leaving);
    },
});
