//! Tiny fixture for the model conveyor.

/* Outer block comment.
   /* Nested block comment. */
   The `fn ignored` text below is inside a comment and must not be parsed:
   fn ignored() { panic!("not real") }
*/

use std::collections::BTreeSet;

/// Roles a subject can hold.
pub enum Role {
    Admin,
    Auditor,
    User,
}

/// A role set with a hard limit.
///
/// Must never hold more roles than `max_roles`.
pub struct Permissions {
    roles: BTreeSet<Role>,
    max_roles: usize,
    audit: Vec<String>,
    unused_note: String,
}

impl Permissions {
    pub fn new(max_roles: usize) -> Self {
        Self {
            roles: BTreeSet::new(),
            max_roles,
            audit: Vec::new(),
            unused_note: String::new(),
        }
    }

    /// Grant a role. Must never exceed the limit.
    pub fn grant(&mut self, role: Role) -> Result<(), String> {
        if self.roles.len() >= self.max_roles {
            return Err("role limit reached".to_string());
        }
        assert!(self.roles.len() <= self.max_roles);
        self.roles.insert(role);
        self.audit.push("grant".to_string());
        Ok(())
    }

    pub fn revoke(&mut self, role: Role) -> bool {
        if role == Role::Admin {
            return false;
        }
        self.roles.remove(&role)
    }

    /// Reset the set. The caller already holds the write lock.
    pub fn reset(&mut self) {
        self.roles.clear();
        self.audit.clear();
    }

    pub fn len(&self) -> usize {
        self.roles.len()
    }
}

/// A reviewer interface. The method without a body is the case that broke the
/// first real run: an operation with no body must still get empty collections,
/// never a bare list.
pub trait Reviewer {
    /// Must be called before every audit write.
    fn before_audit(&mut self);

    /// Default body counts as an operation with effects.
    fn describe(&self) -> String {
        String::from("reviewer")
    }
}

const BANNER: &str = r#"raw "quoted" text \n is not an escape"#;

pub fn first<'a>(items: &'a [Role]) -> Option<&'a Role> {
    items.first()
}

const QUOTE: char = '\'';
