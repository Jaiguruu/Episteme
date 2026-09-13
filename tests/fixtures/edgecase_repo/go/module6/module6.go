package module6

import (
	"fmt"

	"example.com/pkg/module5"
)

type Base6 struct {
	Name string
}

type Service6 struct {
	Base6
}

type Handler6 interface {
	Handle(payload string) bool
}

func (s *Service6) Handle(payload string) bool {
	s.validate(payload)
	fmt.Println(payload)
	return true
}

func (s *Service6) validate(payload string) {
}

func Helper6(value string) string {
	_ = module5.Helper5("x")
	return value
}
