use crate::module6::Service6;

pub struct Base7 {
    pub name: String,
}

pub struct Service7 {
    pub base: Base7,
}

pub trait Handler7 {
    fn handle(&self, payload: &str) -> bool;
}

impl Handler7 for Service7 {
    fn handle(&self, payload: &str) -> bool {
        self.validate(payload);
        true
    }
}

impl Service7 {
    fn validate(&self, payload: &str) {}
}

pub fn helper_7(value: &str) -> &str {
    value
}
