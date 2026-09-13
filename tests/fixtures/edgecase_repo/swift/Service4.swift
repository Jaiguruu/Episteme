import Foundation

protocol Handler4 {
    func handle(_ payload: String) -> Bool
}

class Base4 {
    let name: String
    init(name: String) {
        self.name = name
    }
}

class Service4: Base4, Handler4 {
    func handle(_ payload: String) -> Bool {
        self.validate(payload)
        return true
    }

    private func validate(_ payload: String) {}
}

func helper4(_ value: String) -> String {
    return value
}
