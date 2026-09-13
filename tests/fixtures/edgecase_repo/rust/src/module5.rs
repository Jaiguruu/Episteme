use crate::module4::Service4;

pub struct Base5 {
    pub name: String,
}

pub struct Service5 {
    pub base: Base5,
}

pub trait Handler5 {
    fn handle(&self, payload: &str) -> bool;
}

impl Handler5 for Service5 {
    fn handle(&self, payload: &str) -> bool {
        self.validate(payload);
        true
    }
}

impl Service5 {
    fn validate(&self, payload: &str) {}
}

pub fn helper_5(value: &str) -> &str {
    value
}
