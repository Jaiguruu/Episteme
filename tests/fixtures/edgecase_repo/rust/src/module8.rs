use crate::module7::Service7;

pub struct Base8 {
    pub name: String,
}

pub struct Service8 {
    pub base: Base8,
}

pub trait Handler8 {
    fn handle(&self, payload: &str) -> bool;
}

impl Handler8 for Service8 {
    fn handle(&self, payload: &str) -> bool {
        self.validate(payload);
        true
    }
}

impl Service8 {
    fn validate(&self, payload: &str) {}
}

pub fn helper_8(value: &str) -> &str {
    value
}
