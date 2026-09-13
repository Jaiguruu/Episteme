package module3

import (
	"fmt"

	"example.com/pkg/module2"
)

type Base3 struct {
	Name string
}

type Service3 struct {
	Base3
}

type Handler3 interface {
	Handle(payload string) bool
}

func (s *Service3) Handle(payload string) bool {
	s.validate(payload)
	fmt.Println(payload)
	return true
}

func (s *Service3) validate(payload string) {
}

func Helper3(value string) string {
	_ = module2.Helper2("x")
	return value
}
