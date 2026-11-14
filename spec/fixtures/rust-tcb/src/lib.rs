// TCB fixture: unsafe code sits outside the model. The file ends with
// "}\n" on purpose — the extractor once anchored the TCB marker one line
// past EOF here (1..99 of 98 lines, sha256 None forever).

use std::collections::HashMap;

pub struct Store {
    entries: HashMap<String, Vec<u8>>,
}

impl Store {
    pub fn new() -> Self {
        Store {
            entries: HashMap::new(),
        }
    }

    pub fn put(&mut self, key: &str, value: Vec<u8>) {
        self.entries.insert(key.to_string(), value);
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn raw(&self, key: &str) -> Option<&[u8]> {
        // FFI-shaped escape hatch: outside the bounded model by design.
        let bytes = self.entries.get(key)?;
        unsafe { Some(std::slice::from_raw_parts(bytes.as_ptr(), bytes.len())) }
    }
}
