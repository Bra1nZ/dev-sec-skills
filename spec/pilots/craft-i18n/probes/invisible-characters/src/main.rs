//! Does `read_catalog` reject invisible formatting characters in a row?
//!
//! Evidence for C-08 (open) in ../../claims.yaml and CELL-002. Each case is one
//! catalog line with a character a translator could paste by accident (or on
//! purpose) that is invisible in an editor but changes how the UI renders.

fn main() {
    // context <TAB> English source <TAB> translation
    let cases: [(&str, &str); 5] = [
        ("bidi override U+202E", "\tSave\tEnregistrer\u{202e}\n"),
        ("zero-width space U+200B", "\tSave\tEnregistrer\u{200b}\n"),
        ("left-to-right isolate U+2066", "\tSave\tEnregistrer\u{2066}\n"),
        ("BOM U+FEFF inside the row", "\tSave\tEnregistrer\u{feff}\n"),
        ("control character U+0007 (BEL)", "\tSave\tEnregistrer\u{0007}\n"),
    ];
    for (label, text) in cases {
        let (rows, problems) = craft_i18n_tests::catalog::read_catalog(text, 2);
        let kept = rows
            .first()
            .map(|row| format!("{:?}", row.translation))
            .unwrap_or_default();
        println!(
            "{label}: rows={} problems={:?} kept={}",
            rows.len(),
            problems,
            kept
        );
    }
}
