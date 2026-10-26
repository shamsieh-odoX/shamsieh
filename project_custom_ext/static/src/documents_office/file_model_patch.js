/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FileModel } from "@web/core/file_viewer/file_model";
import { browser } from "@web/core/browser/browser";
import { url } from "@web/core/utils/urls";
import { isOfficeFile } from "./office_mimetypes";

patch(FileModel.prototype, {
    get isOffice() {
        return isOfficeFile(this.mimetype, this.name);
    },

    get isViewable() {
        return super.isViewable || this.isOffice;
    },

    get defaultSource() {
        if (this.isOffice) {
            const route = url(this.urlRoute, this.urlQueryParams);
            const absolute = route.startsWith("http")
                ? route
                : `${browser.location.origin}${route}`;
            return `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(absolute)}`;
        }
        return super.defaultSource;
    },
});
