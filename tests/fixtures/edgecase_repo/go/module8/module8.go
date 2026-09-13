package module8

import (
	"fmt"

	"example.com/pkg/module7"
)

type Base8 struct {
	Name string
}

type Service8 struct {
	Base8
}

type Handler8 interface {
	Handle(payload string) bool
}

func (s *Service8) Handle(payload string) bool {
	s.validate(payload)
	fmt.Println(payload)
	return true
}

func (s *Service8) validate(payload string) {
}

func Helper8(value string) string {
	_ = module7.Helper7("x")
	return value
}
