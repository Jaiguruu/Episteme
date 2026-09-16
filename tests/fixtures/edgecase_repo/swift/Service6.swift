import Foundation

protocol Handler6 {
    func handle(_ payload: String) -> Bool
}

class Base6 {
    let name: String
    init(name: String) {
        self.name = name
    }
}

class Service6: Base6, Handler6 {
    func handle(_ payload: String) -> Bool {
        self.validate(payload)
        return true
    }

    private func validate(_ payload: String) {}
}

func helper6(_ value: String) -> String {
    return value
}
