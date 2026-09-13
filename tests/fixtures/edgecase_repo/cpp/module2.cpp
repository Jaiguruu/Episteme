#include <string>
#include "module1.hpp"

namespace gen {

class Base2 {
public:
    std::string name;
};

class Service2 : public Base2 {
public:
    bool handle(const std::string &payload) {
        this->validate(payload);
        return true;
    }

    void validate(const std::string &payload) {}
};

int helper_2(int value) { return value; }

}  // namespace gen
