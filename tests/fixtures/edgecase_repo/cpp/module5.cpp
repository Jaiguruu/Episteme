#include <string>
#include "module4.hpp"

namespace gen {

class Base5 {
public:
    std::string name;
};

class Service5 : public Base5 {
public:
    bool handle(const std::string &payload) {
        this->validate(payload);
        return true;
    }

    void validate(const std::string &payload) {}
};

int helper_5(int value) { return value; }

}  // namespace gen
