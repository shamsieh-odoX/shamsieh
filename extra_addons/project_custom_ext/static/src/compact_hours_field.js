/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

/**
 * Display float hours as compact durations: 40m, 1h, 1h 30m.
 */
export function formatCompactHours(hours) {
    if (hours === false || hours === null || hours === undefined) {
        return "";
    }
    const value = Number(hours);
    if (!value || Number.isNaN(value)) {
        return "0m";
    }
    const totalMinutes = Math.round(Math.abs(value) * 60);
    const h = Math.floor(totalMinutes / 60);
    const m = totalMinutes % 60;
    const sign = value < 0 ? "-" : "";
    if (h && m) {
        return `${sign}${h}h ${m}m`;
    }
    if (h) {
        return `${sign}${h}h`;
    }
    return `${sign}${m}m`;
}

export class CompactHoursField extends Component {
    static template = "project_custom_ext.CompactHoursField";
    static props = {
        ...standardFieldProps,
        digits: { optional: true },
    };

    get formattedValue() {
        return formatCompactHours(this.props.record.data[this.props.name]);
    }
}

registry.category("fields").add("compact_hours", {
    component: CompactHoursField,
    supportedTypes: ["float"],
    isEmpty: () => false,
});
