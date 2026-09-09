<script>
    export let eyebrow = 'F1 intelligence';
    export let title = '';
    export let description = '';
    export let accent = 'race';
</script>

<header class="page-header {accent}">
    <div class="copy">
        <div class="eyebrow"><span aria-hidden="true"></span>{eyebrow}</div>
        <h1>{title}</h1>
        {#if description}<p>{description}</p>{/if}
    </div>
    {#if $$slots.actions}<div class="actions"><slot name="actions" /></div>{/if}
</header>

<style>
    .page-header {
        position: relative;
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 2rem;
        min-height: 14rem;
        margin: 0 0 1.75rem;
        padding: clamp(1.5rem, 3.5vw, 3rem);
        overflow: hidden;
        border: 1px solid rgba(160, 174, 201, 0.2);
        border-radius: 1.15rem;
        background:
            linear-gradient(105deg, rgba(255, 64, 80, 0.16), transparent 48%),
            linear-gradient(155deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.015));
        box-shadow: 0 24px 65px rgba(0, 0, 0, 0.22);
        isolation: isolate;
    }
    .page-header::after {
        position: absolute;
        z-index: -1;
        top: -7rem;
        right: -4rem;
        width: 25rem;
        height: 20rem;
        border: 4rem solid rgba(255, 64, 80, 0.08);
        border-radius: 50%;
        transform: skewX(-17deg);
        content: '';
    }
    .page-header.drivers {
        background:
            linear-gradient(105deg, rgba(50, 211, 244, 0.14), transparent 48%),
            linear-gradient(155deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.015));
    }
    .page-header.drivers::after { border-color: rgba(50, 211, 244, 0.07); }
    .page-header.strategy {
        background:
            linear-gradient(105deg, rgba(167, 139, 250, 0.15), transparent 48%),
            linear-gradient(155deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.015));
    }
    .page-header.strategy::after { border-color: rgba(167, 139, 250, 0.07); }
    .page-header.trust {
        background:
            linear-gradient(105deg, rgba(70, 211, 154, 0.13), transparent 48%),
            linear-gradient(155deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.015));
    }
    .page-header.trust::after { border-color: rgba(70, 211, 154, 0.07); }
    .copy { max-width: 54rem; }
    .eyebrow {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        margin-bottom: 0.75rem;
        color: #b2bdcc;
        font-size: 0.72rem;
        font-weight: 780;
        letter-spacing: 0.13em;
        text-transform: uppercase;
    }
    .eyebrow span {
        width: 1.7rem;
        height: 0.18rem;
        border-radius: 999px;
        background: #ff4050;
    }
    .drivers .eyebrow span { background: #32d3f4; }
    .strategy .eyebrow span { background: #a78bfa; }
    .trust .eyebrow span { background: #46d39a; }
    h1 {
        max-width: 17ch;
        margin: 0;
        color: #f8fafc;
        font-size: clamp(2.15rem, 5vw, 4.35rem);
        font-weight: 820;
        letter-spacing: -0.055em;
        line-height: 0.98;
    }
    p {
        max-width: 66ch;
        margin: 1rem 0 0;
        color: #adb8c8;
        font-size: clamp(1rem, 1.4vw, 1.12rem);
        line-height: 1.6;
    }
    .actions {
        display: flex;
        flex: none;
        gap: 0.6rem;
        flex-wrap: wrap;
    }
    :global(.actions > div) { display: flex; gap: .6rem; flex-wrap: wrap; }
    :global(.actions a) {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 2.75rem;
        padding: 0.6rem 0.9rem;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 0.65rem;
        background: rgba(255, 255, 255, 0.06);
        color: #f8fafc !important;
        font-size: 0.86rem;
        font-weight: 700;
        text-decoration: none !important;
    }
    :global(.actions a:first-child) { border-color: transparent; background: #ff4050; }
    @media (max-width: 760px) {
        .page-header { align-items: flex-start; flex-direction: column; min-height: 0; }
        .actions { width: 100%; }
        :global(.actions > div) { width: 100%; }
        :global(.actions a) { flex: 1; }
    }
</style>
