package module4

import (
	"fmt"

	"example.com/pkg/module3"
)

type Base4 struct {
	Name string
}

type Service4 struct {
	Base4
}

type Handler4 interface {
	Handle(payload string) bool
}

func (s *Service4) Handle(payload string) bool {
	s.validate(payload)
	fmt.Println(payload)
	return true
}

func (s *Service4) validate(payload string) {
}

func Helper4(value string) string {
	_ = module3.Helper3("x")
	return value
}
