/** @odoo-module **/

import { registry } from "@web/core/registry";
import { BooleanField, booleanField } from "@web/views/fields/boolean/boolean_field";

export class ShamsTodoDoneCheckmark extends BooleanField {
    static template = "shams_todo_groups.ShamsTodoDoneCheckmark";

    async onDoneToggled() {
        const fieldName = this.props.name;
        const newValue = !this.props.record.data[fieldName];

        if (this.props.record.isNew) {
            await this.props.record.update({ [fieldName]: newValue });
            return;
        }

        await this.env.services.orm.write(
            this.props.record.resModel,
            [this.props.record.resId],
            { [fieldName]: newValue },
        );
        await this.props.record.load();

        if (newValue) {
            const root = this.props.record.model.root;
            if (root?.resModel === "shams.todo.dashboard") {
                await root.load();
            }
        }
    }
}

export const shamsTodoDoneCheckmark = {
    ...booleanField,
    component: ShamsTodoDoneCheckmark,
};

registry.category("fields").add("shams_todo_done_checkmark", shamsTodoDoneCheckmark);
