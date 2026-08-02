/** @odoo-module **/

import { Component, onWillStart, useState, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const ICON_MAP = {
    sun: "fa-sun",
    star: "fa-star",
    calendar: "fa-calendar",
    user: "fa-user",
};

export class ShamsTodoApp extends Component {
    static template = "shams_todo_groups.TodoApp";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.addInput = useRef("addInput");
        this.newListInput = useRef("newListInput");

        this.state = useState({
            loading: true,
            listKey: "my_day",
            groupId: false,
            title: _t("My Day"),
            today: "",
            currentUserId: false,
            smartLists: [],
            groups: [],
            tasks: [],
            selectedTask: null,
            newTaskName: "",
            newListName: "",
            showNewList: false,
            showShare: false,
            shareMembers: [],
            shareCandidates: [],
            canShareList: false,
            addMemberId: "",
            defaultGroupId: false,
            detail: {
                name: "",
                is_done: false,
                is_important: false,
                due_date: "",
                priority: "1",
                description_text: "",
                in_my_day: false,
                assigned_user_id: "",
            },
        });

        onWillStart(async () => {
            await this.loadBoard("my_day");
        });
    }

    iconClass(icon) {
        return ICON_MAP[icon] || "fa-list";
    }

    formatDate(iso) {
        if (!iso) {
            return "";
        }
        try {
            return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
                weekday: "short",
                month: "short",
                day: "numeric",
            });
        } catch {
            return iso;
        }
    }

    formatTodayLabel() {
        if (!this.state.today) {
            return "";
        }
        try {
            return new Date(`${this.state.today}T00:00:00`).toLocaleDateString(undefined, {
                weekday: "long",
                month: "long",
                day: "numeric",
            });
        } catch {
            return this.state.today;
        }
    }

    applyBoard(data, keepSelection = true) {
        const selectedId = keepSelection && this.state.selectedTask ? this.state.selectedTask.id : null;
        this.state.today = data.today;
        this.state.listKey = data.list_key;
        this.state.groupId = data.group_id || false;
        this.state.title = data.title;
        this.state.currentUserId = data.current_user_id || false;
        this.state.smartLists = data.smart_lists || [];
        this.state.groups = data.groups || [];
        this.state.tasks = data.tasks || [];
        this.state.defaultGroupId = data.default_group_id || false;
        this.state.canShareList = !!data.can_share_list;
        this.state.shareMembers = data.share_members || [];
        this.state.shareCandidates = data.share_candidates || [];
        if (this.state.listKey !== "group") {
            this.state.showShare = false;
        }

        let selected = data.selected_task || null;
        if (!selected && selectedId) {
            selected = this.state.tasks.find((t) => t.id === selectedId) || null;
        }
        this.state.selectedTask = selected;
        if (selected) {
            this.syncDetailFromTask(selected);
        } else {
            this.state.detail = {
                name: "",
                is_done: false,
                is_important: false,
                due_date: "",
                priority: "1",
                description_text: "",
                in_my_day: false,
                assigned_user_id: "",
            };
        }
        this.state.loading = false;
    }

    syncDetailFromTask(task) {
        this.state.detail = {
            name: task.name || "",
            is_done: !!task.is_done,
            is_important: !!task.is_important,
            due_date: task.due_date || "",
            priority: task.priority || "1",
            description_text: task.description_text || "",
            in_my_day: !!task.in_my_day,
            assigned_user_id: task.assigned_user_id ? String(task.assigned_user_id) : "",
        };
    }

    get assignableMembers() {
        return this.state.selectedTask?.assignable_members || [];
    }

    async loadBoard(listKey, groupId = false, taskId = null) {
        this.state.loading = true;
        try {
            const data = await this.orm.call("shams.todo.task", "get_todo_board", [], {
                list_key: listKey,
                group_id: groupId || null,
                task_id: taskId,
            });
            this.applyBoard(data, !taskId);
        } catch (error) {
            this.state.loading = false;
            this.notification.add(error.message || _t("Could not load To Do board."), {
                type: "danger",
            });
        }
    }

    async selectSmartList(listKey) {
        await this.loadBoard(listKey, false);
    }

    async selectGroup(groupId) {
        await this.loadBoard("group", groupId);
    }

    async selectTask(task) {
        this.state.selectedTask = task;
        this.syncDetailFromTask(task);
    }

    closeDetail() {
        this.state.selectedTask = null;
    }

    toggleShare() {
        this.state.showShare = !this.state.showShare;
    }

    async onToggleDone(task, ev) {
        ev.stopPropagation();
        const data = await this.orm.call("shams.todo.task", "update_todo_from_board", [
            task.id,
            {
                is_done: !task.is_done,
                list_key: this.state.listKey,
                group_id: this.state.groupId || false,
            },
        ]);
        this.applyBoard(data);
    }

    async onToggleImportant(task, ev) {
        ev.stopPropagation();
        const data = await this.orm.call("shams.todo.task", "update_todo_from_board", [
            task.id,
            {
                is_important: !task.is_important,
                list_key: this.state.listKey,
                group_id: this.state.groupId || false,
            },
        ]);
        this.applyBoard(data);
    }

    async onAddTask(ev) {
        ev.preventDefault();
        const name = (this.state.newTaskName || "").trim();
        if (!name) {
            return;
        }
        const groupId =
            this.state.listKey === "group" ? this.state.groupId : this.state.defaultGroupId || null;
        try {
            const data = await this.orm.call("shams.todo.task", "create_todo_from_board", [
                name,
                this.state.listKey,
                groupId,
            ]);
            this.state.newTaskName = "";
            this.applyBoard(data);
            if (this.addInput.el) {
                this.addInput.el.focus();
            }
        } catch (error) {
            this.notification.add(error.data?.message || error.message || _t("Could not create task."), {
                type: "danger",
            });
        }
    }

    async onCreateList(ev) {
        ev.preventDefault();
        const name = (this.state.newListName || "").trim();
        if (!name) {
            return;
        }
        try {
            const group = await this.orm.call("shams.todo.group", "create_list_from_board", [name]);
            this.state.newListName = "";
            this.state.showNewList = false;
            await this.selectGroup(group.id);
        } catch (error) {
            this.notification.add(error.data?.message || error.message || _t("Could not create list."), {
                type: "danger",
            });
        }
    }

    openNewList() {
        this.state.showNewList = true;
        setTimeout(() => this.newListInput.el?.focus(), 0);
    }

    async onAddMember(ev) {
        ev.preventDefault();
        if (!this.state.groupId || !this.state.addMemberId) {
            return;
        }
        try {
            await this.orm.call("shams.todo.group", "add_member_from_board", [
                [this.state.groupId],
                parseInt(this.state.addMemberId, 10),
            ]);
            this.state.addMemberId = "";
            await this.loadBoard("group", this.state.groupId, this.state.selectedTask?.id || null);
            this.notification.add(_t("List shared. You can assign tasks to this person."), {
                type: "success",
            });
        } catch (error) {
            this.notification.add(error.data?.message || error.message || _t("Could not share list."), {
                type: "danger",
            });
        }
    }

    async onRemoveMember(memberId) {
        if (!this.state.groupId) {
            return;
        }
        try {
            await this.orm.call("shams.todo.group", "remove_member_from_board", [
                [this.state.groupId],
                memberId,
            ]);
            await this.loadBoard("group", this.state.groupId, this.state.selectedTask?.id || null);
        } catch (error) {
            this.notification.add(error.data?.message || error.message || _t("Could not update members."), {
                type: "danger",
            });
        }
    }

    async saveDetail() {
        if (!this.state.selectedTask) {
            return;
        }
        const detail = this.state.detail;
        try {
            const data = await this.orm.call("shams.todo.task", "update_todo_from_board", [
                this.state.selectedTask.id,
                {
                    name: detail.name,
                    is_done: detail.is_done,
                    is_important: detail.is_important,
                    due_date: detail.due_date || false,
                    priority: detail.priority,
                    description_text: detail.description_text,
                    my_day_date: detail.in_my_day ? this.state.today : false,
                    assigned_user_id: detail.assigned_user_id
                        ? parseInt(detail.assigned_user_id, 10)
                        : false,
                    list_key: this.state.listKey,
                    group_id: this.state.groupId || false,
                },
            ]);
            this.applyBoard(data);
        } catch (error) {
            this.notification.add(error.data?.message || error.message || _t("Could not save task."), {
                type: "danger",
            });
        }
    }

    isSmartActive(key) {
        return this.state.listKey === key;
    }

    isGroupActive(groupId) {
        return this.state.listKey === "group" && this.state.groupId === groupId;
    }
}

registry.category("actions").add("shams_todo_app", ShamsTodoApp);
