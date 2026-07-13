/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

export class HomePinDialog extends Component {
    static template = "hr_attendance_custom_ext.HomePinDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        onSuccess: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({
            pinCode: "",
            error: false,
            processing: false,
        });
    }

    get dialogTitle() {
        return _t("Home PIN Check In");
    }

    get instructions() {
        return _t("Enter your personal home attendance PIN to complete check in.");
    }

    get pinPlaceholder() {
        return _t("PIN code");
    }

    get cancelLabel() {
        return _t("Cancel");
    }

    get checkingLabel() {
        return _t("Checking...");
    }

    get submitLabel() {
        return _t("Check In with PIN");
    }

    async submitPin() {
        if (this.state.processing) {
            return;
        }
        this.state.processing = true;
        this.state.error = false;
        try {
            const result = await rpc("/hr_attendance_custom/home_pin_check_in", {
                pin_code: this.state.pinCode,
            });
            if (result.status !== "passed") {
                this.state.error = result.message || _t("PIN check-in failed.");
                return;
            }
            if (this.props.onSuccess) {
                await this.props.onSuccess(result);
            }
            this.props.close();
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("PIN check-in failed.");
        } finally {
            this.state.processing = false;
        }
    }
}
