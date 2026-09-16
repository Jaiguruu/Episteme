use crate::module1::Service1;

pub struct Base2 {
    pub name: String,
}

pub struct Service2 {
    pub base: Base2,
}

pub trait Handler2 {
    fn handle(&self, payload: &str) -> bool;
}

impl Handler2 for Service2 {
    fn handle(&self, payload: &str) -> bool {
        self.validate(payload);
        true
    }
}

impl Service2 {
    fn validate(&self, payload: &str) {}
}

pub fn helper_2(value: &str) -> &str {
    value
}
