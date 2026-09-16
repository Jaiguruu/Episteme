local mod2 = require("module2")

local Base3 = {}
Base3.__index = Base3

function Base3.new(name)
  local self = setmetatable({}, Base3)
  self.name = name
  return self
end

local Service3 = setmetatable({}, { __index = Base3 })

function Service3:handle(payload)
  self:validate(payload)
  return true
end

function Service3:validate(payload)
  return payload ~= nil
end

local function helper3(value)
  return value
end

return Service3
