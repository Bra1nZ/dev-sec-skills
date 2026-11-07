//! Compare an independent model of the row grammar with the real
//! `craft_i18n_tests::catalog::read_catalog` over a declared bounded space.
//!
//! The model lives in `model.rs`. This file only generates inputs, calls both
//! sides, and reports differences. It never edits either side: a divergence is
//! printed with its input so a human can decide whether the model or the
//! implementation is wrong.
//!
//! The bound is a vocabulary, not a character count: every row is one of a
//! declared set of context/source/translation tokens, one of a small set of
//! column arities, or one of a set of two/three-line catalogs, and each
//! generated text is wrapped five ways (plain, BOM, CRLF, BOM+CRLF, trailing
//! newline). The size is printed and asserted, so a later edit cannot silently
//! shrink the space.
//!
//! `--mutants` runs the same comparison with one named rule of the model broken
//! at a time. Every broken model must produce at least one divergence; a
//! surviving mutant means the space is blind to that rule.

mod model;

use model::{read, Ruleset};
use std::collections::{BTreeMap, HashSet};
use std::process::ExitCode;

const TARGET: &str = include_str!("../TARGET");
const MAX_INPUT_BYTES: usize = 256;
const DECLARED_MAX_INPUTS: usize = 100_000;
const MAX_REPORTED_DIVERGENCES: usize = 5;

// ---------------------------------------------------------------- vocabulary

const CONTEXTS: &[&str] = &[
    "", "menu", "@id", "@msg", "@plural", "@nope", "@", "menu ", "@id ", "@msg ",
];

const SOURCES: &[&str] = &[
    "",
    "Save",
    "Save…",
    "Open",
    "…",
    "{x}",
    "{x} file",
    "file {x}",
    "{x} and {y}",
    "{x}{y}",
    "Open {a}{b}",
    "{x",
    "Open {a",
    "x}",
    "a\\nb",
    "a\\tb",
    "a\\\\b",
    "a\\qb",
    "a\\",
    "{n} page|{n} pages",
    "page|pages",
    "{n} page",
    "{n} a|{n} b|c",
    "a|b",
    "a||b",
    "{a} to {b}",
    "A\rB",
    "A\u{1}B",
    "\u{feff}A",
    "a b",
];

const TRANSLATIONS: &[&str] = &[
    "",
    "Enregistrer",
    "Ouvrir…",
    "Ouvrir",
    "{x}",
    "{y} fichier",
    "fichier {x}",
    "{y} et {x}",
    "{x}{y}",
    "Ouvrir {a}{b}",
    "{x",
    "Ouvrir {a",
    "x}",
    "a\\nb",
    "a\\tb",
    "a\\\\b",
    "a\\qb",
    "a\\",
    "{n} page|{n} pages",
    "{n} x|y",
    "{n} x",
    "{n} x|{n} y|{n} z",
    "x|y",
    "A\u{1}B",
    "\u{feff}A",
];

const COLUMNS: &[&str] = &[
    "",
    "Save",
    "Enregistrer",
    "@id",
    "{x}",
    "a\\q",
    "\u{1}",
    "a…",
];

/// Lines that exercise one rule each, used two and three at a time so the
/// duplicate key, the line number and the "bad row is left out" behaviour are
/// compared as a sequence rather than one row at a time.
const ROWS: &[&str] = &[
    "",
    "# note",
    "\tSave\tEnregistrer",
    "menu\tSave\tEnregistrer",
    "\tSave\tSauver",
    "menu\tOpen\tOuvrir",
    "\tA\tB",
    "@id\tfile.save\tEnregistrer",
    "@id\t{x}\tfichier",
    "@msg\tOpen {a}{b}\tOuvrir {a}{b}",
    "@nope\tA\tB",
    "\tA\tA\tB",
    "\t\tB",
    "\tA\t",
    "\tA\\q\tB",
    "\r",
    "\u{feff}",
    "A\u{1}B\tC\tD",
    "\t{n} page|{n} pages\t{n} page|{n} pages",
];

/// A smaller subset for the three-line space.
const TRIPLE_ROWS: &[&str] = &[
    "",
    "# note",
    "\tSave\tEnregistrer",
    "\tSave\tSauver",
    "menu\tOpen\tOuvrir",
    "@nope\tA\tB",
    "\t\tB",
    "\tA\t",
    "\tA\\q\tB",
    "\tA\tA\tB",
    "\u{feff}",
];

const PLURAL_SOURCES: &[&str] = &[
    "{n} page|{n} pages",
    "page|pages",
    "{n} page",
    "a|b",
    "a||b",
    "{n} a|{n} b|c",
    "{n} a|{m} b",
];

const PLURAL_TRANSLATIONS: &[&str] = &[
    "{n} page|{n} pages",
    "{n} x|y",
    "{n} x",
    "{n} x|{n} y|{n} z",
    "x|y",
    "x",
    "",
];

// ------------------------------------------------------------------- inputs

#[derive(Clone)]
struct Case {
    text: String,
    forms: usize,
    family: &'static str,
}

struct Space {
    cases: Vec<Case>,
    generated: usize,
    families: BTreeMap<&'static str, usize>,
}

/// Five file-level wrappers for the same logical lines. A single-line catalog
/// is the common case, so CRLF and a trailing newline are exercised there too.
fn wrappers(lines: &[String]) -> Vec<String> {
    let joined = lines.join("\n");
    let crlf = format!("{}\r\n", lines.join("\r\n"));
    vec![
        joined.clone(),
        format!("\u{feff}{joined}"),
        crlf.clone(),
        format!("\u{feff}{crlf}"),
        format!("{joined}\n"),
    ]
}

fn add(cases: &mut Vec<Case>, lines: &[String], forms: usize, family: &'static str) {
    for text in wrappers(lines) {
        assert!(
            text.len() <= MAX_INPUT_BYTES,
            "generated input exceeds the declared {MAX_INPUT_BYTES}-byte bound: {text:?}"
        );
        cases.push(Case {
            text,
            forms,
            family,
        });
    }
}

fn for_each_tuple(arity: usize, f: &mut dyn FnMut(&[&'static str])) {
    let mut indices = vec![0usize; arity];
    loop {
        let tuple: Vec<&'static str> = indices.iter().map(|&i| COLUMNS[i]).collect();
        f(&tuple);
        if arity == 0 {
            return;
        }
        let mut position = arity;
        loop {
            position -= 1;
            indices[position] += 1;
            if indices[position] < COLUMNS.len() {
                break;
            }
            indices[position] = 0;
            if position == 0 {
                return;
            }
        }
    }
}

fn build_cases() -> Vec<Case> {
    let mut cases = Vec::new();

    for &context in CONTEXTS {
        for &source in SOURCES {
            for &translation in TRANSLATIONS {
                let line = format!("{context}\t{source}\t{translation}");
                add(&mut cases, &[line], 2, "single-row");
            }
        }
    }

    for arity in 0..=4usize {
        for_each_tuple(arity, &mut |columns| {
            let line = columns.join("\t");
            add(&mut cases, &[line], 2, "columns");
        });
    }
    for line in ["a\tb\tc\td\te", "\t\t\t\t", "@id\tx\ty\tz\tw"] {
        add(&mut cases, &[line.to_string()], 2, "columns");
    }

    for &first in ROWS {
        for &second in ROWS {
            add(
                &mut cases,
                &[first.to_string(), second.to_string()],
                2,
                "pair",
            );
        }
    }

    for &first in TRIPLE_ROWS {
        for &second in TRIPLE_ROWS {
            for &third in TRIPLE_ROWS {
                add(
                    &mut cases,
                    &[first.to_string(), second.to_string(), third.to_string()],
                    2,
                    "triple",
                );
            }
        }
    }

    for forms in 1..=3usize {
        for &source in PLURAL_SOURCES {
            for &translation in PLURAL_TRANSLATIONS {
                let line = format!("@plural\t{source}\t{translation}");
                add(&mut cases, &[line], forms, "plural");
            }
        }
    }

    cases
}

fn prepare() -> Space {
    let raw = build_cases();
    let generated = raw.len();
    let mut seen = HashSet::new();
    let mut cases = Vec::new();
    let mut families = BTreeMap::new();
    for case in raw {
        if !seen.insert((case.text.clone(), case.forms)) {
            continue;
        }
        *families.entry(case.family).or_insert(0usize) += 1;
        cases.push(case);
    }
    assert!(
        cases.len() <= DECLARED_MAX_INPUTS,
        "space has {} inputs, above the declared bound of {DECLARED_MAX_INPUTS}",
        cases.len()
    );
    Space {
        cases,
        generated,
        families,
    }
}

// --------------------------------------------------------------- comparison

#[derive(Debug, PartialEq, Eq)]
struct View {
    rows: Vec<(usize, String, String, String)>,
    rejected: Vec<usize>,
    problems: Vec<String>,
}

fn actual_view(text: &str, forms: usize) -> Result<View, String> {
    let (rows, problems) = craft_i18n_tests::catalog::read_catalog(text, forms);
    let rows = rows
        .into_iter()
        .map(|row| (row.line, row.context, row.source, row.translation))
        .collect();
    let mut rejected = Vec::with_capacity(problems.len());
    for problem in &problems {
        let line = problem
            .strip_prefix("line ")
            .and_then(|rest| rest.split(':').next())
            .and_then(|number| number.parse::<usize>().ok())
            .ok_or_else(|| format!("unparseable problem: {problem:?}"))?;
        rejected.push(line);
    }
    Ok(View {
        rows,
        rejected,
        problems,
    })
}

fn model_view(text: &str, forms: usize, rules: Ruleset) -> View {
    let catalog = read(text, forms, rules);
    View {
        rows: catalog
            .rows
            .into_iter()
            .map(|row| (row.line, row.context, row.source, row.translation))
            .collect(),
        rejected: catalog.rejected,
        problems: Vec::new(),
    }
}

struct Finding {
    case: Case,
    model: View,
    actual: Result<View, String>,
}

fn run(space: &Space, rules: Ruleset, limit: usize) -> (usize, Vec<Finding>) {
    let mut total = 0usize;
    let mut findings = Vec::new();
    for case in &space.cases {
        let model = model_view(&case.text, case.forms, rules);
        let actual = actual_view(&case.text, case.forms);
        let differs = match &actual {
            Ok(view) => model.rows != view.rows || model.rejected != view.rejected,
            Err(_) => true,
        };
        if differs {
            total += 1;
            if findings.len() < limit {
                findings.push(Finding {
                    case: case.clone(),
                    model,
                    actual,
                });
            }
        }
    }
    (total, findings)
}

fn print_finding(index: usize, finding: &Finding) {
    println!("DIVERGENCE {index}");
    println!("  family: {}", finding.case.family);
    println!("  forms: {}", finding.case.forms);
    println!("  input: {:?}", finding.case.text);
    println!("  model rows: {:?}", finding.model.rows);
    println!("  model rejected: {:?}", finding.model.rejected);
    match &finding.actual {
        Ok(view) => {
            println!("  actual rows: {:?}", view.rows);
            println!("  actual rejected: {:?}", view.rejected);
            println!("  actual problems: {:?}", view.problems);
        }
        Err(error) => println!("  actual error: {error}"),
    }
}

// ------------------------------------------------------------------ coverage

#[derive(Default)]
struct Coverage {
    inputs: usize,
    forms_1: usize,
    forms_2: usize,
    forms_3: usize,
    accepted_rows: usize,
    with_rejection: usize,
    rejection_after_line_1: usize,
    with_bom: usize,
    with_cr: usize,
    with_control: usize,
    multi_line: usize,
}

impl Coverage {
    fn first_gap(&self) -> Option<&'static str> {
        if self.inputs == 0 {
            return Some("inputs");
        }
        if self.forms_1 == 0 || self.forms_2 == 0 || self.forms_3 == 0 {
            return Some("plural forms 1/2/3");
        }
        if self.accepted_rows == 0 {
            return Some("accepted rows");
        }
        if self.with_rejection == 0 {
            return Some("inputs with a rejected line");
        }
        if self.rejection_after_line_1 == 0 {
            return Some("a rejected line after line 1");
        }
        if self.with_bom == 0 {
            return Some("a BOM");
        }
        if self.with_cr == 0 {
            return Some("a carriage return");
        }
        if self.with_control == 0 {
            return Some("a control character");
        }
        if self.multi_line == 0 {
            return Some("a multi-line catalog");
        }
        None
    }
}

fn coverage(space: &Space) -> Coverage {
    let mut stats = Coverage {
        inputs: space.cases.len(),
        ..Coverage::default()
    };
    for case in &space.cases {
        match case.forms {
            1 => stats.forms_1 += 1,
            2 => stats.forms_2 += 1,
            3 => stats.forms_3 += 1,
            _ => {}
        }
        if case.text.contains('\u{feff}') {
            stats.with_bom += 1;
        }
        if case.text.contains('\r') {
            stats.with_cr += 1;
        }
        if case
            .text
            .chars()
            .any(|c| c.is_control() && c != '\t' && c != '\n')
        {
            stats.with_control += 1;
        }
        if case.text.split('\n').count() > 1 {
            stats.multi_line += 1;
        }
        let model = read(&case.text, case.forms, Ruleset::Correct);
        stats.accepted_rows += model.rows.len();
        if !model.rejected.is_empty() {
            stats.with_rejection += 1;
        }
        if model.rejected.iter().any(|&line| line > 1) {
            stats.rejection_after_line_1 += 1;
        }
    }
    stats
}

// ------------------------------------------------------------------ reporting

fn print_header(space: &Space) {
    println!(
        "c02-row-model {} — independent model of the craft-i18n catalog row grammar",
        env!("CARGO_PKG_VERSION")
    );
    println!("target:");
    for line in TARGET.lines() {
        println!("  {line}");
    }
    println!(
        "declared bound: <= {DECLARED_MAX_INPUTS} inputs, <= {MAX_INPUT_BYTES} bytes each, \
         forms in {{1,2,3}}, 5 BOM/line-ending wrappers, {} named mutants",
        Ruleset::MUTANTS.len()
    );
    let families: Vec<String> = space
        .families
        .iter()
        .map(|(name, count)| format!("{name}={count}"))
        .collect();
    println!(
        "space: generated={}, unique={}, families=[{}]",
        space.generated,
        space.cases.len(),
        families.join(", ")
    );
}

fn print_coverage(stats: &Coverage) {
    println!(
        "coverage: inputs={}, forms=1:{} 2:{} 3:{}, accepted-rows={}, \
         inputs-with-a-rejected-line={}, rejection-after-line-1={}, bom={}, cr={}, \
         control={}, multi-line={}",
        stats.inputs,
        stats.forms_1,
        stats.forms_2,
        stats.forms_3,
        stats.accepted_rows,
        stats.with_rejection,
        stats.rejection_after_line_1,
        stats.with_bom,
        stats.with_cr,
        stats.with_control,
        stats.multi_line
    );
}

fn run_correct() -> ExitCode {
    let space = prepare();
    print_header(&space);
    let stats = coverage(&space);
    print_coverage(&stats);
    if let Some(gap) = stats.first_gap() {
        println!("COVERAGE GAP: the space does not exercise {gap}");
        return ExitCode::from(1);
    }
    let (total, findings) = run(&space, Ruleset::Correct, MAX_REPORTED_DIVERGENCES);
    for (index, finding) in findings.iter().enumerate() {
        print_finding(index + 1, finding);
    }
    if total > findings.len() {
        println!(
            "... {} more divergence(s) not shown",
            total - findings.len()
        );
    }
    println!("divergences: {total}");
    if total == 0 {
        println!("RESULT: OK — the model and read_catalog agree on every generated input");
        ExitCode::SUCCESS
    } else {
        println!("RESULT: FAIL — the model and the implementation disagree");
        ExitCode::from(1)
    }
}

fn run_mutant(space: &Space, rules: Ruleset) -> ExitCode {
    let (total, findings) = run(space, rules, 1);
    if let Some(finding) = findings.first() {
        print_finding(1, finding);
    }
    if total == 0 {
        println!(
            "mutant {}: SURVIVED — the space is blind to this edit",
            rules.name()
        );
        ExitCode::from(1)
    } else {
        println!("mutant {}: CAUGHT by {total} input(s)", rules.name());
        ExitCode::SUCCESS
    }
}

fn run_mutants() -> ExitCode {
    let space = prepare();
    print_header(&space);
    println!("mutation control: every named edit to the model must produce a divergence");
    let mut caught = 0usize;
    let mut first_finding: Option<Finding> = None;
    for &rules in Ruleset::MUTANTS {
        let (total, findings) = run(&space, rules, 1);
        if total == 0 {
            println!(
                "mutant {}: SURVIVED — the space is blind to this edit",
                rules.name()
            );
        } else {
            caught += 1;
            println!("mutant {}: CAUGHT by {total} input(s)", rules.name());
            if first_finding.is_none() {
                if let Some(finding) = findings.into_iter().next() {
                    first_finding = Some(finding);
                }
            }
        }
    }
    if let Some(finding) = first_finding {
        println!("first counterexample (from the first caught mutant):");
        print_finding(1, &finding);
    }
    println!("mutants: {caught}/{} caught", Ruleset::MUTANTS.len());
    if caught == Ruleset::MUTANTS.len() {
        println!("RESULT: OK — the bounded space detects every named model edit");
        ExitCode::SUCCESS
    } else {
        println!("RESULT: FAIL — at least one model edit is invisible to the space");
        ExitCode::from(1)
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.as_slice() {
        [] => run_correct(),
        [flag] if flag == "--mutants" => run_mutants(),
        [flag] if flag == "--list-mutants" => {
            for &rules in Ruleset::MUTANTS {
                println!("{}", rules.name());
            }
            ExitCode::SUCCESS
        }
        [flag, name] if flag == "--mutant" => {
            match Ruleset::MUTANTS
                .iter()
                .copied()
                .find(|rules| rules.name() == name)
            {
                Some(rules) => {
                    let space = prepare();
                    print_header(&space);
                    run_mutant(&space, rules)
                }
                None => {
                    eprintln!("unknown mutant {name:?}; run --list-mutants");
                    ExitCode::from(2)
                }
            }
        }
        _ => {
            eprintln!("usage: c02-row-model [--mutants | --mutant NAME | --list-mutants]");
            ExitCode::from(2)
        }
    }
}
