use crate::module5::Service5;

pub struct Base6 {
    pub name: String,
}

pub struct Service6 {
    pub base: Base6,
}

pub trait Handler6 {
    fn handle(&self, payload: &str) -> bool;
}

impl Handler6 for Service6 {
    fn handle(&self, payload: &str) -> bool {
        self.validate(payload);
        true
    }
}

impl Service6 {
    fn validate(&self, payload: &str) {}
}

pub fn helper_6(value: &str) -> &str {
    value
}
