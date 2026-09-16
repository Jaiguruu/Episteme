package module7

import (
	"fmt"

	"example.com/pkg/module6"
)

type Base7 struct {
	Name string
}

type Service7 struct {
	Base7
}

type Handler7 interface {
	Handle(payload string) bool
}

func (s *Service7) Handle(payload string) bool {
	s.validate(payload)
	fmt.Println(payload)
	return true
}

func (s *Service7) validate(payload string) {
}

func Helper7(value string) string {
	_ = module6.Helper6("x")
	return value
}
