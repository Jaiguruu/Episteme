#include <string>
#include "module5.hpp"

namespace gen {

class Base6 {
public:
    std::string name;
};

class Service6 : public Base6 {
public:
    bool handle(const std::string &payload) {
        this->validate(payload);
        return true;
    }

    void validate(const std::string &payload) {}
};

int helper_6(int value) { return value; }

}  // namespace gen
