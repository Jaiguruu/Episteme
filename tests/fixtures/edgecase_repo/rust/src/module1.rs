use crate::module0::Service0;

pub struct Base1 {
    pub name: String,
}

pub struct Service1 {
    pub base: Base1,
}

pub trait Handler1 {
    fn handle(&self, payload: &str) -> bool;
}

impl Handler1 for Service1 {
    fn handle(&self, payload: &str) -> bool {
        self.validate(payload);
        true
    }
}

impl Service1 {
    fn validate(&self, payload: &str) {}
}

pub fn helper_1(value: &str) -> &str {
    value
}
