/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { download } from "@web/core/network/download";
import { DocumentsKanbanController } from "@documents/views/kanban/documents_kanban_controller";
import { DocumentsListController } from "@documents/views/list/documents_list_controller";
import { isOfficeRecord } from "./office_mimetypes";

/**
 * Documents only opens the FileViewer when isViewable() is true.
 * Word/Excel/PPT return false, so a click does nothing.
 * Mark Office files as viewable; fall back to download if needed.
 */
function patchRecordClass(RecordClass) {
    const proto = RecordClass?.prototype;
    if (!proto || proto.__officeIsViewablePatched) {
        return;
    }
    proto.__officeIsViewablePatched = true;

    const descriptor = Object.getOwnPropertyDescriptor(proto, "isViewable");
    if (descriptor?.get) {
        Object.defineProperty(proto, "isViewable", {
            configurable: true,
            enumerable: descriptor.enumerable,
            get() {
                return descriptor.get.call(this) || isOfficeRecord(this);
            },
        });
        return;
    }
    if (typeof proto.isViewable === "function") {
        const original = proto.isViewable;
        proto.isViewable = function (...args) {
            return original.apply(this, args) || isOfficeRecord(this);
        };
        return;
    }
    // Method may live further up the chain (e.g. FileModelMixin).
    proto.isViewable = function (...args) {
        const parent = Object.getPrototypeOf(proto);
        const parentFn = parent && parent.isViewable;
        const base =
            typeof parentFn === "function" ? parentFn.apply(this, args) : false;
        return base || isOfficeRecord(this);
    };
}

function ensureOfficeOpen(superOpenRecord, record, options) {
    if (record?.constructor) {
        patchRecordClass(record.constructor);
    }
    const result = superOpenRecord(record, options);
    // If Documents still ignores non-viewable Office files, download instead.
    if (record && isOfficeRecord(record)) {
        const viewable =
            typeof record.isViewable === "function"
                ? record.isViewable()
                : record.isViewable;
        if (!viewable) {
            download({
                data: {},
                url: `/documents/content/${record.resId}`,
            });
        }
    }
    return result;
}

function patchController(Controller) {
    patch(Controller.prototype, {
        setup() {
            super.setup(...arguments);
            const Record = this.model?.constructor?.Record;
            if (Record) {
                patchRecordClass(Record);
            }
        },
        openRecord(record, options) {
            return ensureOfficeOpen(super.openRecord.bind(this), record, options);
        },
    });
}

patchController(DocumentsKanbanController);
patchController(DocumentsListController);
