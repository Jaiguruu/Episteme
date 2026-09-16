package module2

import (
	"fmt"

	"example.com/pkg/module1"
)

type Base2 struct {
	Name string
}

type Service2 struct {
	Base2
}

type Handler2 interface {
	Handle(payload string) bool
}

func (s *Service2) Handle(payload string) bool {
	s.validate(payload)
	fmt.Println(payload)
	return true
}

func (s *Service2) validate(payload string) {
}

func Helper2(value string) string {
	_ = module1.Helper1("x")
	return value
}
