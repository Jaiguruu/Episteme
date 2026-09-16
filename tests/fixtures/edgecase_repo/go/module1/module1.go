package module1

import (
	"fmt"

	"example.com/pkg/module0"
)

type Base1 struct {
	Name string
}

type Service1 struct {
	Base1
}

type Handler1 interface {
	Handle(payload string) bool
}

func (s *Service1) Handle(payload string) bool {
	s.validate(payload)
	fmt.Println(payload)
	return true
}

func (s *Service1) validate(payload string) {
}

func Helper1(value string) string {
	_ = module0.Helper0("x")
	return value
}
