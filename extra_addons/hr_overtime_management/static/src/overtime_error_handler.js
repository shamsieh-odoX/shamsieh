/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { RPCError } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { UncaughtPromiseError } from "@web/core/errors/error_service";
import { FormController } from "@web/views/form/form_controller";

const OVERTIME_EXCEPTIONS = new Set([
    "odoo.exceptions.AccessError",
    "odoo.exceptions.UserError",
    "odoo.exceptions.ValidationError",
]);

const OVERTIME_MODEL_RE = /^hr\.overtime(\.|$)/;

function isOvertimeContextError(error) {
    if (error.model && OVERTIME_MODEL_RE.test(error.model)) {
        return true;
    }
    const text = `${error.data?.message || ""} ${error.message || ""}`;
    return /hr\.overtime/i.test(text) || /\bres\.company\b/i.test(text);
}

export function friendlyOvertimeErrorMessage(error) {
    const raw = error.data?.message || error.message || "";
    const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);

    if (lines.some((l) => /res\.company/i.test(l)) || lines.some((l) => /company rule employee/i.test(l))) {
        return _t(
            "This record uses a company you are not assigned to. " +
            "Only select projects from your own company, then save again."
        );
    }

    const accessLine = lines.find((l) => /doesn'?t have/i.test(l));
    if (accessLine) {
        const resourceLine = lines.find((l) => l.startsWith("-"));
        const resource = resourceLine ? resourceLine.replace(/^-\s*/, "") : _t("this record");
        return _t("You cannot access %(resource)s for this overtime request.", { resource });
    }

    const withoutBoilerplate = lines.filter((l) => !/top-secret|Uh-oh|stumbled upon/i.test(l));
    return withoutBoilerplate[0] || _t("This overtime action is not allowed.");
}

function notificationTitle(error) {
    const name = error.exceptionName || error.data?.name || "";
    if (name.includes("ValidationError")) {
        return _t("Validation");
    }
    if (name.includes("AccessError")) {
        return _t("Company access");
    }
    return _t("Overtime");
}

function showOvertimeNotification(env, error) {
    env.services.notification.add(friendlyOvertimeErrorMessage(error), {
        type: "warning",
        title: notificationTitle(error),
        sticky: false,
    });
}

function isHandledOvertimeError(error) {
    const name = error.exceptionName || error.data?.name || "";
    return OVERTIME_EXCEPTIONS.has(name);
}

function overtimeRpcErrorHandler(env, error, originalError) {
    if (!(error instanceof UncaughtPromiseError) || !(originalError instanceof RPCError)) {
        return false;
    }
    if (!isHandledOvertimeError(originalError)) {
        return false;
    }
    if (!isOvertimeContextError(originalError)) {
        return false;
    }
    error.unhandledRejectionEvent.preventDefault();
    showOvertimeNotification(env, originalError);
    return true;
}

registry.category("error_handlers").add("overtimeRpcErrorHandler", overtimeRpcErrorHandler, {
    sequence: 95,
});

patch(FormController.prototype, {
    async onSaveError(error, callbacks, leaving) {
        const resModel = this.model.root.resModel;
        if (resModel?.startsWith("hr.overtime") && isHandledOvertimeError(error)) {
            showOvertimeNotification(this.env, error);
            return;
        }
        return super.onSaveError(error, callbacks, leaving);
    },
});
