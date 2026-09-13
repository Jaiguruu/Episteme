import Foundation

protocol Handler2 {
    func handle(_ payload: String) -> Bool
}

class Base2 {
    let name: String
    init(name: String) {
        self.name = name
    }
}

class Service2: Base2, Handler2 {
    func handle(_ payload: String) -> Bool {
        self.validate(payload)
        return true
    }

    private func validate(_ payload: String) {}
}

func helper2(_ value: String) -> String {
    return value
}
