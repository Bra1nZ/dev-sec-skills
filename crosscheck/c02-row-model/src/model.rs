//! Independent executable model of the craft-i18n catalog row grammar.
//!
//! The source of truth is `docs/catalog-format.md` in the craft-i18n checkout
//! plus the C-02 claim: a malformed row is rejected and a valid one still
//! loads. This is a second implementation, not a translation of
//! `crates/craft-i18n-tests/src/catalog.rs`. `main.rs` compares the two over a
//! declared bounded space; a divergence is a finding, never a reason to edit
//! this file until it agrees.
//!
//! Where the format document is silent, the model states its own rule instead
//! of reading the implementation's:
//!
//! * a control character other than TAB, or a byte-order mark inside a row,
//!   makes the row malformed: the format lets `\n` and `\t` be written only as
//!   escapes, so a literal one is not representable;
//! * a BOM is tolerated only at the start of the file, where a UTF-8 signature
//!   can be; a BOM at the start of a later line is inside a row;
//! * a `\r` at the end of a line is a line ending and is removed once; a `\r`
//!   inside a field is a control character;
//! * a comment line starts with `#` in its first column; `#` elsewhere is
//!   literal text;
//! * a row is keyed by `(context, source)` after unescaping, so two rows that
//!   differ only in the translation collide.

use std::collections::HashSet;

/// A row the model accepts, with its columns unescaped.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Row {
    /// 1-based line number in the file.
    pub line: usize,
    pub context: String,
    pub source: String,
    pub translation: String,
}

/// What the model says about one catalog.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct Catalog {
    pub rows: Vec<Row>,
    /// 1-based line numbers the model rejects, in line order.
    pub rejected: Vec<usize>,
}

/// The contexts the format gives a meaning to.
const RESERVED: &[&str] = &["@plural", "@id", "@msg"];

/// One named edit to the correct rules.
///
/// `Correct` is the model under test. Every other variant disables exactly one
/// rule, so `main.rs --mutants` can prove that the comparison notices a wrong
/// model. A mutant that survives means the bounded space is blind to that rule.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Ruleset {
    Correct,
    NoColumnCheck,
    NoEmptySource,
    NoEmptyTranslation,
    NoDuplicateKey,
    NoUnknownEscape,
    NoTrailingBackslash,
    NoUnknownContext,
    NoPlaceholderCheck,
    NoEllipsisCheck,
    NoTemplateAdjacent,
    NoTemplateLiteral,
    NoTemplateOpen,
    NoPluralSource,
    NoPluralForms,
    NoPluralPlaceholders,
    NoControlChars,
    NoMidBom,
    NoFileBomStrip,
    IdNotExempt,
    OffByOneLine,
    NoCommentSkip,
    NoCrStrip,
}

impl Ruleset {
    /// Every mutant, in the order the harness reports them.
    pub const MUTANTS: &'static [Ruleset] = &[
        Ruleset::NoColumnCheck,
        Ruleset::NoEmptySource,
        Ruleset::NoEmptyTranslation,
        Ruleset::NoDuplicateKey,
        Ruleset::NoUnknownEscape,
        Ruleset::NoTrailingBackslash,
        Ruleset::NoUnknownContext,
        Ruleset::NoPlaceholderCheck,
        Ruleset::NoEllipsisCheck,
        Ruleset::NoTemplateAdjacent,
        Ruleset::NoTemplateLiteral,
        Ruleset::NoTemplateOpen,
        Ruleset::NoPluralSource,
        Ruleset::NoPluralForms,
        Ruleset::NoPluralPlaceholders,
        Ruleset::NoControlChars,
        Ruleset::NoMidBom,
        Ruleset::NoFileBomStrip,
        Ruleset::IdNotExempt,
        Ruleset::OffByOneLine,
        Ruleset::NoCommentSkip,
        Ruleset::NoCrStrip,
    ];

    pub fn name(self) -> &'static str {
        match self {
            Ruleset::Correct => "correct",
            Ruleset::NoColumnCheck => "no-column-check",
            Ruleset::NoEmptySource => "no-empty-source",
            Ruleset::NoEmptyTranslation => "no-empty-translation",
            Ruleset::NoDuplicateKey => "no-duplicate-key",
            Ruleset::NoUnknownEscape => "no-unknown-escape",
            Ruleset::NoTrailingBackslash => "no-trailing-backslash",
            Ruleset::NoUnknownContext => "no-unknown-context",
            Ruleset::NoPlaceholderCheck => "no-placeholder-check",
            Ruleset::NoEllipsisCheck => "no-ellipsis-check",
            Ruleset::NoTemplateAdjacent => "no-template-adjacent",
            Ruleset::NoTemplateLiteral => "no-template-literal",
            Ruleset::NoTemplateOpen => "no-template-open",
            Ruleset::NoPluralSource => "no-plural-source",
            Ruleset::NoPluralForms => "no-plural-forms",
            Ruleset::NoPluralPlaceholders => "no-plural-placeholders",
            Ruleset::NoControlChars => "no-control-chars",
            Ruleset::NoMidBom => "no-mid-bom",
            Ruleset::NoFileBomStrip => "no-file-bom-strip",
            Ruleset::IdNotExempt => "id-not-exempt",
            Ruleset::OffByOneLine => "off-by-one-line",
            Ruleset::NoCommentSkip => "no-comment-skip",
            Ruleset::NoCrStrip => "no-cr-strip",
        }
    }
}

/// Read a catalog whose locale has `forms` plural forms.
pub fn read(text: &str, forms: usize, rules: Ruleset) -> Catalog {
    let text = match rules {
        Ruleset::NoFileBomStrip => text,
        _ => text.strip_prefix('\u{feff}').unwrap_or(text),
    };
    let mut catalog = Catalog::default();
    let mut keys: HashSet<(String, String)> = HashSet::new();
    for (index, raw) in text.split('\n').enumerate() {
        let line_no = match rules {
            Ruleset::OffByOneLine => index,
            _ => index + 1,
        };
        let line = match rules {
            Ruleset::NoCrStrip => raw,
            _ => raw.strip_suffix('\r').unwrap_or(raw),
        };
        if line.is_empty() {
            continue;
        }
        if line.starts_with('#') && rules != Ruleset::NoCommentSkip {
            continue;
        }
        match parse(line_no, line, forms, rules) {
            Some(row) => {
                let key = (row.context.clone(), row.source.clone());
                if rules == Ruleset::NoDuplicateKey || keys.insert(key) {
                    catalog.rows.push(row);
                } else {
                    catalog.rejected.push(line_no);
                }
            }
            None => catalog.rejected.push(line_no),
        }
    }
    catalog
}

fn parse(line: usize, text: &str, forms: usize, rules: Ruleset) -> Option<Row> {
    let columns: Vec<&str> = text.split('\t').collect();
    if rules != Ruleset::NoColumnCheck && columns.len() != 3 {
        return None;
    }

    let invisible = text.chars().any(|c| {
        if c == '\t' {
            return false;
        }
        match rules {
            Ruleset::NoControlChars => false,
            Ruleset::NoMidBom => c.is_control(),
            _ => c.is_control() || c == '\u{feff}',
        }
    });
    if invisible {
        return None;
    }

    let context_raw = columns.first().copied().unwrap_or("");
    let source_raw = columns.get(1).copied().unwrap_or("");
    let translation_raw = columns.get(2).copied().unwrap_or("");
    if source_raw.is_empty() && rules != Ruleset::NoEmptySource {
        return None;
    }

    let context = unescape(context_raw, rules)?;
    let source = unescape(source_raw, rules)?;
    let translation = unescape(translation_raw, rules)?;
    if translation.is_empty() && rules != Ruleset::NoEmptyTranslation {
        return None;
    }

    let id_exempt = rules != Ruleset::IdNotExempt;
    match context.as_str() {
        // The source is a command id, not a template.
        "@id" if id_exempt => {}
        "@plural" => check_plural(&source, &translation, forms, rules)?,
        c if c.starts_with('@') && !RESERVED.contains(&c) && rules != Ruleset::NoUnknownContext => {
            return None;
        }
        _ => {
            if rules != Ruleset::NoPlaceholderCheck
                && placeholders(&source) != placeholders(&translation)
            {
                return None;
            }
            if rules != Ruleset::NoEllipsisCheck
                && source.ends_with('…') != translation.ends_with('…')
            {
                return None;
            }
            if context == "@msg" && !check_template(&source, rules) {
                return None;
            }
        }
    }

    Some(Row {
        line,
        context,
        source,
        translation,
    })
}

/// The documented `@msg` template rules, written as a left-to-right scan.
///
/// A template is malformed when a `{` has no closing `}`, when two
/// placeholders are adjacent, or when it has no literal text at all (so it
/// would match every message).
fn check_template(source: &str, rules: Ruleset) -> bool {
    let mut previous_was_placeholder = false;
    let mut has_literal = false;
    let mut chars = source.chars();
    while let Some(c) = chars.next() {
        if c == '{' {
            if previous_was_placeholder && rules != Ruleset::NoTemplateAdjacent {
                return false;
            }
            let mut closed = false;
            for d in chars.by_ref() {
                if d == '}' {
                    closed = true;
                    break;
                }
            }
            if !closed && rules != Ruleset::NoTemplateOpen {
                return false;
            }
            previous_was_placeholder = true;
        } else {
            has_literal = true;
            previous_was_placeholder = false;
        }
    }
    if source.contains('{') && !has_literal && rules != Ruleset::NoTemplateLiteral {
        return false;
    }
    true
}

/// An `@plural` row: `one|other` English forms, then the locale's `forms`
/// nonempty forms, each with the placeholders of the English `other` form.
fn check_plural(source: &str, translation: &str, forms: usize, rules: Ruleset) -> Option<()> {
    let english: Vec<&str> = source.split('|').collect();
    if rules != Ruleset::NoPluralSource {
        if english.len() != 2 {
            return None;
        }
        let one = english[0];
        let other = english[1];
        if one.is_empty() || other.is_empty() || placeholders(one) != placeholders(other) {
            return None;
        }
    }
    let other_placeholders = if english.len() == 2 {
        placeholders(english[1])
    } else {
        placeholders(source)
    };

    let translated: Vec<&str> = translation.split('|').collect();
    if rules != Ruleset::NoPluralForms {
        if translated.len() != forms || translated.iter().any(|form| form.is_empty()) {
            return None;
        }
    }
    if rules != Ruleset::NoPluralPlaceholders {
        if translated
            .iter()
            .any(|form| placeholders(form) != other_placeholders)
        {
            return None;
        }
    }
    Some(())
}

/// `\n`, `\t` and `\\` are the only escapes.
fn unescape(text: &str, rules: Ruleset) -> Option<String> {
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars();
    while let Some(c) = chars.next() {
        if c != '\\' {
            out.push(c);
            continue;
        }
        match chars.next() {
            Some('n') => out.push('\n'),
            Some('t') => out.push('\t'),
            Some('\\') => out.push('\\'),
            Some(other) => {
                if rules == Ruleset::NoUnknownEscape {
                    out.push(other);
                } else {
                    return None;
                }
            }
            None => {
                if rules != Ruleset::NoTrailingBackslash {
                    return None;
                }
            }
        }
    }
    Some(out)
}

/// `{name}` placeholders, sorted so translations may reorder them.
fn placeholders(text: &str) -> Vec<&str> {
    let mut names = Vec::new();
    let mut rest = text;
    while let Some((_, after_open)) = rest.split_once('{') {
        match after_open.split_once('}') {
            Some((name, after_close)) => {
                names.push(name);
                rest = after_close;
            }
            None => break,
        }
    }
    names.sort_unstable();
    names
}
