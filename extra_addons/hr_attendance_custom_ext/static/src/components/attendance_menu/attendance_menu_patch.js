/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { rpc, ConnectionLostError } from "@web/core/network/rpc";
import { ActivityMenu } from "@hr_attendance/components/attendance_menu/attendance_menu";
import { FaceCheckDialog } from "@hr_attendance_custom_ext/components/face_check_dialog/face_check_dialog";
import { isIosApp } from "@web/core/browser/feature_detection";

patch(ActivityMenu.prototype, {
    async signInOut() {
        this.dropdown.close();
        if (this._attendanceInProgress) {
            return;
        }
        this._attendanceInProgress = true;

        const isCheckIn = !this.state.checkedIn;
        if (isCheckIn && this.employee?.check_in_requires_face) {
            try {
                this.dialogService.add(FaceCheckDialog, {
                    actionType: "check_in",
                    onSuccess: async () => {
                        await this.searchReadEmployee();
                    },
                });
            } finally {
                this._attendanceInProgress = false;
            }
            return;
        }

        if (isCheckIn && this.employee?.check_in_requires_office_geo) {
            if (!this.employee.office_geo_configured) {
                this.notification.add(
                    _t("Office geolocation is not configured. Please contact HR."),
                    { title: _t("Attendance Error"), type: "danger" }
                );
                this._attendanceInProgress = false;
                return;
            }
            await this._officeGeoCheckInOut();
            return;
        }

        return super.signInOut(...arguments);
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
                    title: _t("Attendance Error"),
                    type: "danger",
                });
            }
        } finally {
            this._attendanceInProgress = false;
        }
    },
});
