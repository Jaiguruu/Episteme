package module5

import (
	"fmt"

	"example.com/pkg/module4"
)

type Base5 struct {
	Name string
}

type Service5 struct {
	Base5
}

type Handler5 interface {
	Handle(payload string) bool
}

func (s *Service5) Handle(payload string) bool {
	s.validate(payload)
	fmt.Println(payload)
	return true
}

func (s *Service5) validate(payload string) {
}

func Helper5(value string) string {
	_ = module4.Helper4("x")
	return value
}
