// Dismissable panel shown after a successful export, listing the
// reconciliation notes returned by exportBlueprint() (e.g. "deleted 2
// object(s), 2 work entry(ies)...", "appended 1 duplicated object(s)").
export interface ExportNotesPanelProps {
  notes: string[];
  onDismiss: () => void;
}

export function ExportNotesPanel({ notes, onDismiss }: ExportNotesPanelProps) {
  return (
    <div className="export-notes">
      <div className="export-notes__header">
        <h3>Exported</h3>
        <button type="button" onClick={onDismiss} aria-label="Dismiss">
          ✕
        </button>
      </div>
      {/* Shown on EVERY export, permanently. Before PST v2.2.8 a same-world
          re-import silently destroyed the base in-game (verified 2026-07-16);
          v2.2.8 regenerates the colliding IDs and a same-world import was
          verified intact in-game 2026-07-31 — both in docs/CALIBRATION.md.
          The version condition is the whole warning now: users on an older PST
          are still one import away from losing a 500-hour save, and this
          warning existing only in the README is how that happens. */}
      <div className="export-notes__danger">
        <strong>⚠ Importing back into the world this base came from requires
        PalworldSaveTools v2.2.8 or newer.</strong>{" "}
        Older versions reuse the base's object IDs, and the game silently
        deletes the imported structures on next load. Any PST version is fine
        for importing into a different world. Back up your save folder before
        every import (<code>%LOCALAPPDATA%\Pal\Saved\SaveGames</code>), and make
        sure the game is fully closed whenever PalworldSaveTools saves.
      </div>
      {notes.length === 0 ? (
        <p>No changes to report — the file round-tripped as-is.</p>
      ) : (
        <ul>
          {notes.map((n, i) => (
            // Notes are free-text summary lines, not stable keys; index is fine for a short-lived, append-only list.
            // eslint-disable-next-line react/no-array-index-key
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
