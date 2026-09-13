import Foundation

protocol Handler3 {
    func handle(_ payload: String) -> Bool
}

class Base3 {
    let name: String
    init(name: String) {
        self.name = name
    }
}

class Service3: Base3, Handler3 {
    func handle(_ payload: String) -> Bool {
        self.validate(payload)
        return true
    }

    private func validate(_ payload: String) {}
}

func helper3(_ value: String) -> String {
    return value
}
