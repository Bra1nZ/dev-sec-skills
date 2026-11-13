//! Test code for the review queue. The doctor asserts this file is excluded
//! from decisions.yaml and the review queue without --include-tests.

fn helper_in_tests() -> bool {
    true
}

#[test]
fn a_test_at_the_boundary() {
    assert!(helper_in_tests());
}
