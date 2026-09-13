local mod4 = require("module4")

local Base5 = {}
Base5.__index = Base5

function Base5.new(name)
  local self = setmetatable({}, Base5)
  self.name = name
  return self
end

local Service5 = setmetatable({}, { __index = Base5 })

function Service5:handle(payload)
  self:validate(payload)
  return true
end

function Service5:validate(payload)
  return payload ~= nil
end

local function helper5(value)
  return value
end

return Service5
