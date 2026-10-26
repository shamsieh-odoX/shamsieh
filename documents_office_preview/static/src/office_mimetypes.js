/** @odoo-module **/

export const OFFICE_MIMETYPES = new Set([
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "application/rtf",
    "text/rtf",
]);

export const OFFICE_EXTENSIONS = new Set([
    "doc",
    "docx",
    "docm",
    "xls",
    "xlsx",
    "xlsm",
    "ppt",
    "pptx",
    "pptm",
    "odt",
    "ods",
    "odp",
    "rtf",
]);

export function isOfficeFile(mimetype, name = "") {
    if (mimetype && OFFICE_MIMETYPES.has(mimetype)) {
        return true;
    }
    const ext = String(name || "")
        .split(".")
        .pop()
        ?.toLowerCase();
    return Boolean(ext && OFFICE_EXTENSIONS.has(ext));
}

export function isOfficeRecord(record) {
    const data = record?.data || {};
    return isOfficeFile(
        data.mimetype || record.mimetype || "",
        data.name || data.display_name || record.name || ""
    );
}
