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

/** Site-wide Solar nav: transparent over homepage hero, ink bar otherwise. */
publicWidget.registry.ShamsiehNav = publicWidget.Widget.extend({
    selector: '.shamsieh-site',

    start() {
        this._setupNavScroll();
        return this._super(...arguments);
    },

    destroy() {
        if (this._onScroll) {
            window.removeEventListener('scroll', this._onScroll);
        }
        return this._super(...arguments);
    },

    _setupNavScroll() {
        const headers = this.el.querySelectorAll(':scope > header, header.shamsieh-header, header.o_header_standard');
        if (!headers.length) {
            return;
        }

        headers.forEach((header) => header.classList.add('shamsieh-header'));
        const overHero = Boolean(this.el.querySelector('.shamsieh-home .sh-hero'));

        const update = () => {
            const scrolled = !overHero || window.scrollY > 40;
            headers.forEach((header) => {
                header.classList.toggle('is-scrolled', scrolled);
            });
        };

        this._onScroll = update;
        window.addEventListener('scroll', update, { passive: true });
        update();
    },
});

export default publicWidget.registry.ShamsiehHome;
