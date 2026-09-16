import Foundation

protocol Handler5 {
    func handle(_ payload: String) -> Bool
}

class Base5 {
    let name: String
    init(name: String) {
        self.name = name
    }
}

class Service5: Base5, Handler5 {
    func handle(_ payload: String) -> Bool {
        self.validate(payload)
        return true
    }

    private func validate(_ payload: String) {}
}

func helper5(_ value: String) -> String {
    return value
}
