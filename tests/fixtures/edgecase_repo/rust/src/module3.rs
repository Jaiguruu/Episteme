use crate::module2::Service2;

pub struct Base3 {
    pub name: String,
}

pub struct Service3 {
    pub base: Base3,
}

pub trait Handler3 {
    fn handle(&self, payload: &str) -> bool;
}

impl Handler3 for Service3 {
    fn handle(&self, payload: &str) -> bool {
        self.validate(payload);
        true
    }
}

impl Service3 {
    fn validate(&self, payload: &str) {}
}

pub fn helper_3(value: &str) -> &str {
    value
}
