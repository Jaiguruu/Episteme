import Foundation

protocol Handler1 {
    func handle(_ payload: String) -> Bool
}

class Base1 {
    let name: String
    init(name: String) {
        self.name = name
    }
}

class Service1: Base1, Handler1 {
    func handle(_ payload: String) -> Bool {
        self.validate(payload)
        return true
    }

    private func validate(_ payload: String) {}
}

func helper1(_ value: String) -> String {
    return value
}
