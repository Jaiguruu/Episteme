using System;

namespace Example.Gen
{
    public interface IHandler1
    {
        bool Handle(string payload);
    }

    public class Base1
    {
        protected string Name;
    }

    public class Service1 : Base1, IHandler1
    {
        public Service1(string name)
        {
            this.Name = name;
        }

        public bool Handle(string payload)
        {
            this.Validate(payload);
            return true;
        }

        private void Validate(string payload) { }
    }
}
