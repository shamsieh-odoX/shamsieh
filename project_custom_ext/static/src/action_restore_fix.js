/** @odoo-module **/

/**
 * Guard against corrupted action controller stacks (undefined controller entries)
 * that crash breadcrumb restore with: Cannot read properties of undefined (reading 'virtual').
 * This can happen after failed RPC/save flows or act_window cache refresh on an empty stack.
 */
import { patch } from "@web/core/utils/patch";
import {
    actionService,
    ControllerNotFoundError,
} from "@web/webclient/actions/action_service";

patch(actionService, {
    start(env) {
        const action = super.start(env);
        const originalRestore = action.restore.bind(action);

        action.restore = async function (jsId) {
            try {
                return await originalRestore(jsId);
            } catch (error) {
                const brokenStack =
                    error instanceof TypeError ||
                    error instanceof ControllerNotFoundError ||
                    error?.message?.includes("Invalid controller to restore") ||
                    error?.message?.includes("virtual controller");
                if (brokenStack) {
                    return action.doAction("project.open_view_project_all", {
                        clearBreadcrumbs: true,
                    });
                }
                throw error;
            }
        };

        return action;
    },
});
