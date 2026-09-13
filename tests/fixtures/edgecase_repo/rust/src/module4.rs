use crate::module3::Service3;

pub struct Base4 {
    pub name: String,
}

pub struct Service4 {
    pub base: Base4,
}

pub trait Handler4 {
    fn handle(&self, payload: &str) -> bool;
}

impl Handler4 for Service4 {
    fn handle(&self, payload: &str) -> bool {
        self.validate(payload);
        true
    }
}

impl Service4 {
    fn validate(&self, payload: &str) {}
}

pub fn helper_4(value: &str) -> &str {
    value
}
