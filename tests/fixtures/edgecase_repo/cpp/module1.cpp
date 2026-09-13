#include <string>
#include "module0.hpp"

namespace gen {

class Base1 {
public:
    std::string name;
};

class Service1 : public Base1 {
public:
    bool handle(const std::string &payload) {
        this->validate(payload);
        return true;
    }

    void validate(const std::string &payload) {}
};

int helper_1(int value) { return value; }

}  // namespace gen
