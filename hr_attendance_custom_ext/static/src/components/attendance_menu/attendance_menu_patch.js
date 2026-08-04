/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { rpc, ConnectionLostError } from "@web/core/network/rpc";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ActivityMenu } from "@hr_attendance/components/attendance_menu/attendance_menu";
import { FaceCheckDialog } from "@hr_attendance_custom_ext/components/face_check_dialog/face_check_dialog";
import { HomePinDialog } from "@hr_attendance_custom_ext/components/home_pin_dialog/home_pin_dialog";
import { isIosApp } from "@web/core/browser/feature_detection";

patch(ActivityMenu.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.onBreak = false;
    },

    get labelCheckIn() {
        return _t("Check In");
    },
    get labelCheckOut() {
        return _t("Check Out");
    },
    get labelBreakIn() {
        return _t("Break In");
    },
    get labelBreakOut() {
        return _t("Break Out");
    },
    get labelOnBreak() {
        return _t("On Break");
    },
    get labelWorking() {
        return _t("Working");
    },
    get labelOfficeDayHint() {
        return _t("Office day — use the fingerprint device to check in and out.");
    },
    get labelBreakHint() {
        return _t("You can record Break Out / Break In from Odoo.");
    },
    get labelBefore() {
        return _t("Before");
    },
    get labelSince() {
        return _t("Since");
    },
    get labelTotalToday() {
        return _t("Total today");
    },

    get breakPunchAllowed() {
        if (this.employee?.break_punch_allowed !== undefined) {
            return this.employee.break_punch_allowed !== false;
        }
        return true;
    },

    _searchReadEmployeeFill() {
        super._searchReadEmployeeFill(...arguments);
        if (this.employee?.id) {
            this.state.onBreak = this.employee.hikvision_presence_status === "on_break";
        } else {
            this.state.onBreak = false;
        }
    },

    async punch(punchType) {
        this.dropdown.close();
        if (this._attendanceInProgress) {
            return;
        }
        this._attendanceInProgress = true;
        await this.searchReadEmployee();

        const isBreakPunch = punchType === "break_in" || punchType === "break_out";
        if (isBreakPunch) {
            if (!this.breakPunchAllowed) {
                this.notification.add(this.labelOfficeDayHint, {
                    title: _t("Attendance"),
                    type: "warning",
                });
                this._attendanceInProgress = false;
                return;
            }
        } else if (this.employee?.manual_attendance_allowed === false) {
            this.notification.add(this.labelOfficeDayHint, {
                title: _t("Attendance"),
                type: "warning",
            });
            this._attendanceInProgress = false;
            return;
        }

        if (punchType === "check_in") {
            return this._homeManualCheckIn();
        }

        if (punchType === "check_out") {
            return this._confirmCheckOut();
        }

        try {
            this.employee = await rpc("/hr_attendance_custom/systray_punch", {
                punch_type: punchType,
            });
            this._searchReadEmployeeFill();
        } catch (error) {
            this._handleAttendanceError(error);
        } finally {
            this._attendanceInProgress = false;
        }
    },

    async signInOut() {
        await this.searchReadEmployee();
        if (this.employee?.manual_attendance_allowed === false) {
            this.notification.add(this.labelOfficeDayHint, {
                title: _t("Attendance"),
                type: "warning",
            });
            return;
        }
        if (this.state.checkedIn) {
            return this._confirmCheckOut();
        }
        return this.punch("check_in");
    },

    async _homeManualCheckIn() {
        try {
            this.employee = await rpc("/hr_attendance/systray_check_in_out", {});
            this._searchReadEmployeeFill();
        } catch (error) {
            this._handleAttendanceError(error);
        } finally {
            this._attendanceInProgress = false;
        }
    },

    _handleAttendanceError(error) {
        if (error instanceof ConnectionLostError) {
            this.notification.add(
                _t("Connection lost. Attendance punch could not be recorded."),
                { title: _t("Attendance Error"), type: "danger", sticky: false }
            );
            return;
        }
        const message = error.data?.message || error.message;
        this.notification.add(message || _t("Attendance punch could not be recorded."), {
            title: _t("Attendance Error"),
            type: "danger",
        });
    },

    _confirmCheckOut() {
        const proceed = async () => {
            this._attendanceInProgress = true;
            try {
                this.employee = await rpc("/hr_attendance_custom/systray_punch", {
                    punch_type: "check_out",
                });
                this._searchReadEmployeeFill();
            } catch (error) {
                this._handleAttendanceError(error);
            } finally {
                this._attendanceInProgress = false;
            }
        };

        if (!this.employee?.single_check_in_per_day) {
            return proceed();
        }

        this._attendanceInProgress = false;
        this.dialogService.add(ConfirmationDialog, {
            title: _t("Check out"),
            body: _t(
                "Are you sure you want to check out now? You will not be able to check in again today."
            ),
            confirmLabel: _t("Check out"),
            cancelLabel: _t("Stay checked in"),
            confirm: proceed,
            cancel: () => {
                this._attendanceInProgress = false;
            },
        });
    },

    async _officeGeoPunch(punchType) {
        if (!isIosApp() && navigator.geolocation && navigator.onLine) {
            navigator.geolocation.getCurrentPosition(
                async ({ coords: { latitude, longitude } }) => {
                    try {
                        this.employee = await rpc("/hr_attendance/systray_check_in_out", {
                            latitude,
                            longitude,
                        });
                        this._searchReadEmployeeFill();
                    } catch (error) {
                        this._handleAttendanceError(error);
                    } finally {
                        this._attendanceInProgress = false;
                    }
                },
                () => {
                    this.notification.add(
                        _t("Your device location is required to check in from the office."),
                        { title: _t("Attendance Error"), type: "danger" }
                    );
                    this._attendanceInProgress = false;
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        } else {
            this.notification.add(
                _t("Your device location is required to check in from the office."),
                { title: _t("Attendance Error"), type: "danger" }
            );
            this._attendanceInProgress = false;
        }
    },

    _openFaceCheckDialog() {
        this._attendanceInProgress = false;
        this.dialogService.add(FaceCheckDialog, {
            actionType: "check_in",
            onSuccess: async () => {
                await this.searchReadEmployee();
            },
        });
    },

    _openHomePinDialog() {
        this._attendanceInProgress = false;
        this.dialogService.add(HomePinDialog, {
            onSuccess: async () => {
                await this.searchReadEmployee();
            },
        });
    },

    async checking(latitude = false, longitude = false) {
        try {
            this.employee = await rpc("/hr_attendance/systray_check_in_out", {
                latitude,
                longitude,
            });
            this._searchReadEmployeeFill();
        } catch (error) {
            this._handleAttendanceError(error);
        } finally {
            this._attendanceInProgress = false;
        }
    },
});

