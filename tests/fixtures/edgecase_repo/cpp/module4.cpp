#include <string>
#include "module3.hpp"

namespace gen {

class Base4 {
public:
    std::string name;
};

class Service4 : public Base4 {
public:
    bool handle(const std::string &payload) {
        this->validate(payload);
        return true;
    }

    void validate(const std::string &payload) {}
};

int helper_4(int value) { return value; }

}  // namespace gen
