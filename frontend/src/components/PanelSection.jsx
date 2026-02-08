import React from 'react';

export default function PanelSection({ title, children, defaultOpen = true }) {
    const [open, setOpen] = React.useState(defaultOpen);
    return (
        <div className="panel-section">
            <button className="panel-section__header" onClick={() => setOpen(o => !o)}>
                <span className="panel-section__title">{title}</span>
                <span className="panel-section__chev">{open ? '▾' : '▸'}</span>
            </button>
            {open && (
                <div className="panel-section__body">
                    {children}
                </div>
            )}
        </div>
    );
}
