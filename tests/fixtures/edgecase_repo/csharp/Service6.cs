using System;

namespace Example.Gen
{
    public interface IHandler6
    {
        bool Handle(string payload);
    }

    public class Base6
    {
        protected string Name;
    }

    public class Service6 : Base6, IHandler6
    {
        public Service6(string name)
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
