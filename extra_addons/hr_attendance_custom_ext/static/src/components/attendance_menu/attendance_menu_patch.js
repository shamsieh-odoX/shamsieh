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
    async signInOut() {
        this.dropdown.close();
        if (this._attendanceInProgress) {
            return;
        }
        this._attendanceInProgress = true;

        await this.searchReadEmployee();

        if (this.state.checkedIn) {
            return this._confirmCheckOut();
        }

        if (this.employee?.check_in_requires_face && this.employee?.check_in_requires_home_pin) {
            this._attendanceInProgress = false;
            this.dialogService.add(ConfirmationDialog, {
                title: _t("Choose Check-In Method"),
                body: _t("Use Face Verification or Home PIN to check in."),
                confirmLabel: _t("Face Verification"),
                cancelLabel: _t("Home PIN"),
                confirm: async () => {
                    this._openFaceCheckDialog();
                },
                cancel: () => {
                    this._openHomePinDialog();
                },
            });
            return;
        }

        if (this.employee?.check_in_requires_face) {
            this._openFaceCheckDialog();
            return;
        }

        if (this.employee?.check_in_requires_home_pin) {
            this._openHomePinDialog();
            return;
        }

        if (this.employee?.check_in_requires_office_geo) {
            if (!this.employee.office_geo_configured) {
                this.notification.add(
                    _t("Office geolocation is not configured. Please contact HR."),
                    { title: _t("Attendance Error"), type: "danger" }
                );
                this._attendanceInProgress = false;
                return;
            }
            return this._officeGeoCheckInOut();
        }

        return super.signInOut(...arguments);
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

    _confirmCheckOut() {
        const proceed = async () => {
            this._attendanceInProgress = true;
            await this.checking();
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

    async _officeGeoCheckInOut() {
        if (!isIosApp() && navigator.geolocation && navigator.onLine) {
            navigator.geolocation.getCurrentPosition(
                async ({ coords: { latitude, longitude } }) => {
                    await this.checking(latitude, longitude);
                },
                () => {
                    this.notification.add(
                        _t("Your device location is required to check in from the office."),
                        { title: _t("Attendance Error"), type: "danger" }
                    );
                    this._attendanceInProgress = false;
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                }
            );
        } else {
            this.notification.add(
                _t("Your device location is required to check in from the office."),
                { title: _t("Attendance Error"), type: "danger" }
            );
            this._attendanceInProgress = false;
        }
    },

    async checking(latitude = false, longitude = false) {
        try {
            this.employee = await rpc("/hr_attendance/systray_check_in_out", {
                latitude,
                longitude,
            });
            this._searchReadEmployeeFill();
        } catch (error) {
            if (error instanceof ConnectionLostError) {
                this.notification.add(
                    _t("Connection lost. Check in/out could not be recorded."),
                    {
                        title: _t("Attendance Error"),
                        type: "danger",
                        sticky: false,
                    }
                );
            } else {
                const message = error.data?.message || error.message;
                this.notification.add(message || _t("Check in/out could not be recorded."), {
                    title: _t("Attendance Error"), type: "danger",
                });
            }
        } finally {
            this._attendanceInProgress = false;
        }
    },
});
