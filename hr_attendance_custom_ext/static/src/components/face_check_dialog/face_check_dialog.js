/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

export class FaceCheckDialog extends Component {
    static template = "hr_attendance_custom_ext.FaceCheckDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        onSuccess: { type: Function, optional: true },
        actionType: { type: String, optional: true },
    };

    setup() {
        this.videoRef = useRef("video");
        this.canvasRef = useRef("canvas");
        this.state = useState({ error: false, processing: false });
        this.stream = null;
        onMounted(() => this.startCamera());
        onWillUnmount(() => this.stopCamera());
    }

    get dialogTitle() {
        return _t("Face Verification");
    }

    get instructions() {
        return _t("Position your face in the frame to verify your identity before checking in.");
    }

    get cancelLabel() {
        return _t("Cancel");
    }

    get verifyingLabel() {
        return _t("Verifying...");
    }

    get captureLabel() {
        return _t("Capture & Check In");
    }

    async startCamera() {
        if (!navigator.mediaDevices?.getUserMedia) {
            this.state.error = _t("Camera access is not available in this browser.");
            return;
        }
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "user" },
                audio: false,
            });
            this.videoRef.el.srcObject = this.stream;
        } catch {
            this.state.error = _t("Unable to access the camera. Please allow camera access and try again.");
        }
    }

    stopCamera() {
        if (this.stream) {
            for (const track of this.stream.getTracks()) {
                track.stop();
            }
            this.stream = null;
        }
    }

    _captureImageBase64() {
        const video = this.videoRef.el;
        const canvas = this.canvasRef.el;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext("2d");
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
        return dataUrl.split(",")[1];
    }

    async captureAndVerify() {
        if (this.state.processing || this.state.error) {
            return;
        }
        this.state.processing = true;
        try {
            const selfieImageBase64 = this._captureImageBase64();
            const result = await rpc("/hr_attendance_custom/face/check", {
                action_type: this.props.actionType || "check_in",
                selfie_image_base64: selfieImageBase64,
            });
            if (result.status !== "passed") {
                this.state.error = result.message || _t("Face verification failed.");
                return;
            }
            if (this.props.onSuccess) {
                await this.props.onSuccess(result);
            }
            this.props.close();
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Face verification failed.");
        } finally {
            this.state.processing = false;
        }
    }
}
