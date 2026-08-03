/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { ensureBotifyWidget } from "./botify_widget_loader";

/**
 * Assistant client action — hosts a short status panel and ensures the
 * hosted Botify widget (floating bubble) is loaded for this session.
 */
class BotifyAssistant extends Component {
    static template = "botify_agent.Assistant";
    static props = { "*": true };

    setup() {
        this.botifyWidget = useService("botify_widget");
        this.state = useState({
            ready: false,
            error: null,
            identityReady: false,
        });

        onWillStart(async () => {
            const result = await (this.botifyWidget?.ensure?.() || ensureBotifyWidget());
            if (!result?.ok) {
                this.state.error = result?.error || "Could not load the Botify widget.";
                return;
            }
            this.state.ready = true;
            this.state.identityReady = Boolean(result.identityReady);
        });
    }
}

registry.category("actions").add("botify_agent.assistant", BotifyAssistant);
