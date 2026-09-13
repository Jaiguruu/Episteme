#include <string>
#include "module2.hpp"

namespace gen {

class Base3 {
public:
    std::string name;
};

class Service3 : public Base3 {
public:
    bool handle(const std::string &payload) {
        this->validate(payload);
        return true;
    }

    void validate(const std::string &payload) {}
};

int helper_3(int value) { return value; }

}  // namespace gen
