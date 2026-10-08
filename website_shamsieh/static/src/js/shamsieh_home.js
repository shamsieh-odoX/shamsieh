/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';

publicWidget.registry.ShamsiehHome = publicWidget.Widget.extend({
    selector: '.shamsieh-home',

    start() {
        this._setupReveal();
        this._setupSmoothAnchors();
        return this._super(...arguments);
    },

    _setupReveal() {
        const nodes = this.el.querySelectorAll('.sh-reveal');
        if (!nodes.length) {
            return;
        }
        if (!('IntersectionObserver' in window)) {
            nodes.forEach((node) => node.classList.add('is-visible'));
            return;
        }
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('is-visible');
                        observer.unobserve(entry.target);
                    }
                });
            },
            { rootMargin: '0px 0px -8% 0px', threshold: 0.12 }
        );
        nodes.forEach((node) => observer.observe(node));
    },

    _setupSmoothAnchors() {
        this.el.querySelectorAll('a[href^="#"]').forEach((anchor) => {
            anchor.addEventListener('click', (event) => {
                const id = anchor.getAttribute('href');
                if (!id || id === '#') {
                    return;
                }
                const target = document.querySelector(id);
                if (!target) {
                    return;
                }
                event.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        });
    },
});

export default publicWidget.registry.ShamsiehHome;
