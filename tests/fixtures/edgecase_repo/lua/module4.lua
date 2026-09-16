local mod3 = require("module3")

local Base4 = {}
Base4.__index = Base4

function Base4.new(name)
  local self = setmetatable({}, Base4)
  self.name = name
  return self
end

local Service4 = setmetatable({}, { __index = Base4 })

function Service4:handle(payload)
  self:validate(payload)
  return true
end

function Service4:validate(payload)
  return payload ~= nil
end

local function helper4(value)
  return value
end

return Service4
